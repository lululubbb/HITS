package org.apache.commons.csv;
import org.junit.jupiter.api.Timeout;
import java.io.Serializable;
import java.util.Arrays;
import java.util.Iterator;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;

import java.lang.reflect.Constructor;
import java.lang.reflect.Method;

public class CSVRecord_1_2Test {

    @Test
    @Timeout(8000)
    void testCSVRecordConstructor_withValuesMappingCommentRecordNumber() throws Exception {
        String[] values = new String[]{"val1", "val2"};
        java.util.Map<String, Integer> mapping = new java.util.HashMap<>();
        mapping.put("header1", 0);
        mapping.put("header2", 1);
        String comment = "This is a comment";
        long recordNumber = 10L;

        Constructor<CSVRecord> constructor = CSVRecord.class.getDeclaredConstructor(
                String[].class, java.util.Map.class, String.class, long.class);
        constructor.setAccessible(true);
        CSVRecord record = constructor.newInstance(values, mapping, comment, recordNumber);

        // Validate fields through public methods
        assertEquals("val1", record.get(0));
        assertEquals("val2", record.get(1));
        assertEquals("val1", record.get("header1"));
        assertEquals("val2", record.get("header2"));
        assertEquals(comment, record.getComment());
        assertEquals(recordNumber, record.getRecordNumber());
        assertEquals(2, record.size());
        assertTrue(record.isConsistent());
        assertTrue(record.isMapped("header1"));
        assertTrue(record.isSet("header1"));
        assertFalse(record.isMapped("nonexistent"));
        assertFalse(record.isSet("nonexistent"));
        assertNotNull(record.iterator());
        assertNotNull(record.toString());

        // Validate values() method via reflection (package-private)
        Method valuesMethod = CSVRecord.class.getDeclaredMethod("values");
        valuesMethod.setAccessible(true);
        String[] valuesArray = (String[]) valuesMethod.invoke(record);
        assertArrayEquals(values, valuesArray);
    }

    @Test
    @Timeout(8000)
    void testCSVRecordConstructor_withNullValuesUsesEmptyArray() throws Exception {
        java.util.Map<String, Integer> mapping = java.util.Collections.emptyMap();
        String comment = null;
        long recordNumber = 5L;

        Constructor<CSVRecord> constructor = CSVRecord.class.getDeclaredConstructor(
                String[].class, java.util.Map.class, String.class, long.class);
        constructor.setAccessible(true);
        CSVRecord record = constructor.newInstance((Object) null, mapping, comment, recordNumber);

        assertEquals(0, record.size());
        assertEquals(comment, record.getComment());
        assertEquals(recordNumber, record.getRecordNumber());
        assertFalse(record.isConsistent());
        assertFalse(record.isMapped("any"));
        assertFalse(record.isSet("any"));
        assertNotNull(record.iterator());
        assertNotNull(record.toString());

        Method valuesMethod = CSVRecord.class.getDeclaredMethod("values");
        valuesMethod.setAccessible(true);
        String[] valuesArray = (String[]) valuesMethod.invoke(record);
        assertArrayEquals(new String[0], valuesArray);
    }

}
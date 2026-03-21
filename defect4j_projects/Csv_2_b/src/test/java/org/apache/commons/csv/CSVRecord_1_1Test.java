package org.apache.commons.csv;
import org.junit.jupiter.api.Timeout;
import java.io.Serializable;
import java.util.Arrays;
import java.util.Iterator;

import static org.junit.jupiter.api.Assertions.*;

import org.junit.jupiter.api.Test;

import java.lang.reflect.Constructor;
import java.util.Collections;
import java.util.HashMap;
import java.util.Map;

public class CSVRecord_1_1Test {

    @Test
    @Timeout(8000)
    void testCSVRecordConstructorAndGetters() throws Exception {
        String[] values = new String[]{"val1", "val2"};
        Map<String, Integer> mapping = new HashMap<>();
        mapping.put("col1", 0);
        mapping.put("col2", 1);
        String comment = "comment";
        long recordNumber = 123L;

        Constructor<CSVRecord> constructor = CSVRecord.class.getDeclaredConstructor(
                String[].class, Map.class, String.class, long.class);
        constructor.setAccessible(true);

        CSVRecord record = constructor.newInstance((Object) values, mapping, comment, recordNumber);

        assertArrayEquals(values, record.values());
        assertEquals(comment, record.getComment());
        assertEquals(recordNumber, record.getRecordNumber());
        assertEquals(2, record.size());
        assertEquals("val1", record.get(0));
        assertEquals("val2", record.get(1));
        assertEquals("val1", record.get("col1"));
        assertEquals("val2", record.get("col2"));
        assertTrue(record.isMapped("col1"));
        assertTrue(record.isMapped("col2"));
        assertFalse(record.isMapped("col3"));
        assertTrue(record.isSet("col1"));
        assertFalse(record.isSet("col3"));
        assertTrue(record.isConsistent());
        assertNotNull(record.toString());

        int count = 0;
        for (String val : record) {
            assertEquals(values[count], val);
            count++;
        }
        assertEquals(values.length, count);
    }

    @Test
    @Timeout(8000)
    void testCSVRecordConstructorWithNullValues() throws Exception {
        Map<String, Integer> mapping = Collections.emptyMap();
        String comment = null;
        long recordNumber = 0L;

        Constructor<CSVRecord> constructor = CSVRecord.class.getDeclaredConstructor(
                String[].class, Map.class, String.class, long.class);
        constructor.setAccessible(true);

        CSVRecord record = constructor.newInstance((Object) null, mapping, comment, recordNumber);

        assertNotNull(record.values());
        assertEquals(0, record.size());
        assertTrue(record.isConsistent());
        assertEquals(comment, record.getComment());
        assertEquals(recordNumber, record.getRecordNumber());
        assertFalse(record.iterator().hasNext());
    }
}
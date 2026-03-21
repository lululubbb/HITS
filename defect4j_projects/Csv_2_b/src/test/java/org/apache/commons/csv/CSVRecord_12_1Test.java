package org.apache.commons.csv;
import org.junit.jupiter.api.Timeout;
import java.io.Serializable;
import java.util.Arrays;
import java.util.Iterator;

import static org.junit.jupiter.api.Assertions.*;

import java.lang.reflect.Constructor;
import java.util.Collections;
import java.util.HashMap;
import java.util.Map;

import org.junit.jupiter.api.Test;

class CSVRecord_12_1Test {

    @Test
    @Timeout(8000)
    void testToString_withNonEmptyValues() throws Exception {
        String[] values = new String[] { "a", "b", "c" };
        Map<String, Integer> mapping = new HashMap<>();
        mapping.put("col1", 0);
        mapping.put("col2", 1);
        mapping.put("col3", 2);
        String comment = "comment";
        long recordNumber = 1L;

        CSVRecord record = createCSVRecord(values, mapping, comment, recordNumber);

        String expected = "[a, b, c]";
        assertEquals(expected, record.toString());
    }

    @Test
    @Timeout(8000)
    void testToString_withEmptyValues() throws Exception {
        String[] values = new String[0];
        Map<String, Integer> mapping = Collections.emptyMap();
        String comment = null;
        long recordNumber = 0L;

        CSVRecord record = createCSVRecord(values, mapping, comment, recordNumber);

        String expected = "[]";
        assertEquals(expected, record.toString());
    }

    // Helper method to instantiate CSVRecord via reflection
    private CSVRecord createCSVRecord(String[] values, Map<String, Integer> mapping, String comment, long recordNumber) throws Exception {
        Constructor<CSVRecord> ctor = CSVRecord.class.getDeclaredConstructor(String[].class, Map.class, String.class, long.class);
        ctor.setAccessible(true);
        return ctor.newInstance(values, mapping, comment, recordNumber);
    }
}
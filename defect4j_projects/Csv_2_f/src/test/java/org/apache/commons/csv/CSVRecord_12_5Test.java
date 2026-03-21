package org.apache.commons.csv;
import org.junit.jupiter.api.Timeout;
import java.io.Serializable;
import java.util.Arrays;
import java.util.Iterator;

import static org.junit.jupiter.api.Assertions.assertEquals;

import java.lang.reflect.Constructor;
import java.util.Collections;
import java.util.Map;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

public class CSVRecord_12_5Test {

    private CSVRecord csvRecordWithValues;
    private CSVRecord csvRecordEmptyValues;

    @BeforeEach
    public void setUp() throws Exception {
        // Use reflection to get the constructor since it's package-private
        Constructor<CSVRecord> constructor = CSVRecord.class.getDeclaredConstructor(
                String[].class, Map.class, String.class, long.class);
        constructor.setAccessible(true);

        // Setup CSVRecord with values
        String[] values = new String[] { "a", "b", "c" };
        Map<String, Integer> mapping = Collections.emptyMap();
        csvRecordWithValues = constructor.newInstance((Object) values, mapping, null, 1L);

        // Setup CSVRecord with empty values
        String[] emptyValues = new String[0];
        csvRecordEmptyValues = constructor.newInstance((Object) emptyValues, mapping, null, 2L);
    }

    @Test
    @Timeout(8000)
    public void testToString_withValues() {
        String expected = "[a, b, c]";
        assertEquals(expected, csvRecordWithValues.toString());
    }

    @Test
    @Timeout(8000)
    public void testToString_emptyValues() {
        String expected = "[]";
        assertEquals(expected, csvRecordEmptyValues.toString());
    }
}
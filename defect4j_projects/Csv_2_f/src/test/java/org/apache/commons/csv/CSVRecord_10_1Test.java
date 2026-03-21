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

class CSVRecord_10_1Test {

    private CSVRecord csvRecord;
    private long recordNumber;

    @BeforeEach
    void setUp() throws Exception {
        recordNumber = 123L;

        // Use reflection to access the package-private constructor
        Constructor<CSVRecord> constructor = CSVRecord.class.getDeclaredConstructor(
                String[].class, Map.class, String.class, long.class);
        constructor.setAccessible(true);

        csvRecord = constructor.newInstance(
                (Object) new String[] {"value1", "value2"}, // cast to Object to avoid varargs ambiguity
                Collections.<String, Integer>emptyMap(),
                null,
                recordNumber);
    }

    @Test
    @Timeout(8000)
    void testGetRecordNumber() {
        assertEquals(recordNumber, csvRecord.getRecordNumber());
    }
}